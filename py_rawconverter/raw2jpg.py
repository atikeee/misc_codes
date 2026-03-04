#!/usr/bin/env python3
"""
raw2jpg.py  -  RAW to JPG converter + JPEG rotation tool

MODES
  -c   Convert RAW files to high-quality JPEG
  -r   Rotate JPEGs by star rating, then reset rating to 0
         1 star  -> rotate left  (90 CCW)
         2 stars -> rotate right (90 CW)
         other   -> skip, do not touch

TARGET
  -f FILE        single file
  -d DIRECTORY   all matching files, recursively

EXAMPLES
  python raw2jpg.py -c -f photo.cr2
  python raw2jpg.py -c -d C:\\shoot
  python raw2jpg.py -r -f photo.jpg
  python raw2jpg.py -r -d C:\\shoot\\converted

DEPENDENCIES
  pip install rawpy pillow pyyaml piexif
  Optional for best CR3 support: exiftool (https://exiftool.org)
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import struct
import subprocess
import sys
from pathlib import Path

# ── optional dependencies ─────────────────────────────────────────────────────

def _require(package, pip_name=None):
    import importlib
    try:
        return importlib.import_module(package)
    except ImportError:
        print(f"[ERROR] '{package}' not installed.  Run: pip install {pip_name or package}",
              file=sys.stderr)
        sys.exit(1)

_require("rawpy"); _require("yaml", "pyyaml"); _require("PIL", "pillow")

import rawpy, yaml
from PIL import Image, ImageEnhance, ImageFilter

try:
    import piexif
    _HAS_PIEXIF = True
except ImportError:
    _HAS_PIEXIF = False

# ── constants ─────────────────────────────────────────────────────────────────

RAW_EXTENSIONS = {
    ".cr2", ".cr3", ".nef", ".nrw", ".arw", ".srf", ".sr2", ".dng",
    ".orf", ".rw2", ".raf", ".pef", ".ptx", ".3fr", ".mef", ".mrw",
    ".x3f", ".erf", ".rwl", ".srw", ".kdc", ".dcr",
}

try:
    _T         = Image.Transpose
    _ORIENT_OP = {
        2: _T.FLIP_LEFT_RIGHT, 3: _T.ROTATE_180,  4: _T.FLIP_TOP_BOTTOM,
        5: _T.TRANSPOSE,       6: _T.ROTATE_270,   7: _T.TRANSVERSE,
        8: _T.ROTATE_90,
    }
    _ROT_LEFT  = _T.ROTATE_90    # 90 CCW
    _ROT_RIGHT = _T.ROTATE_270   # 90 CW
except AttributeError:           # Pillow < 9.1
    _ORIENT_OP = {
        2: Image.FLIP_LEFT_RIGHT, 3: Image.ROTATE_180,  4: Image.FLIP_TOP_BOTTOM,
        5: Image.TRANSPOSE,       6: Image.ROTATE_270,   7: Image.TRANSVERSE,
        8: Image.ROTATE_90,
    }
    _ROT_LEFT  = Image.ROTATE_90
    _ROT_RIGHT = Image.ROTATE_270

_ORIENT_DESC = {
    1: "Normal", 2: "Flip H", 3: "180", 4: "Flip V",
    5: "90CW+flip", 6: "90CW", 7: "90CCW+flip", 8: "90CCW",
}

# ── default config ────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "output":  {"directory": ""},
    "jpeg":    {"quality": 95, "subsampling": 0, "optimize": True,
                "embed_icc_profile": True},
    "colour":  {"brightness": 1.0, "contrast": 1.0, "saturation": 1.0,
                "sharpening": 1},
    "logging": {"level": "INFO", "log_file": "conversion.log"},
}

def _merge(base, over):
    result = dict(base)
    for k, v in over.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result

def load_config(path):
    if path is None:
        candidate = Path(__file__).with_name("config.yaml")
        path = str(candidate) if candidate.exists() else None
    if path is None:
        print("[CONFIG] Using built-in defaults", flush=True)
        return DEFAULT_CONFIG
    print(f"[CONFIG] {path}", flush=True)
    with open(path, encoding="utf-8") as fh:
        user = yaml.safe_load(fh) or {}
    cfg = _merge(DEFAULT_CONFIG, user)
    print(f"[CONFIG] output.directory = '{cfg['output']['directory']}'", flush=True)
    return cfg

def setup_logging(cfg):
    lc  = cfg.get("logging", {})
    lvl = getattr(logging, lc.get("level", "INFO").upper(), logging.INFO)
    handlers = [logging.StreamHandler(sys.stdout)]
    if lc.get("log_file"):
        handlers.append(logging.FileHandler(lc["log_file"], encoding="utf-8"))
    logging.basicConfig(level=lvl,
                        format="%(asctime)s  %(levelname)-8s  %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                        handlers=handlers)

# ═════════════════════════════════════════════════════════════════════════════
# SHARED: JPEG marker iterator
# ═════════════════════════════════════════════════════════════════════════════

def _iter_markers(data: bytes):
    """Yield (b1, payload, offset, seg_len) for every JPEG marker before SOS."""
    i = 2  # skip SOI
    while i + 3 < len(data):
        b0, b1 = data[i], data[i+1]
        if b0 != 0xFF:
            break
        if b1 in (0xD8,0xD9,0xD0,0xD1,0xD2,0xD3,0xD4,0xD5,0xD6,0xD7):
            i += 2
            continue
        if b1 == 0xDA:   # SOS - image data starts, stop
            break
        seg_len = (data[i+2] << 8) | data[i+3]
        if seg_len < 2:
            break
        payload = data[i+4: i+2+seg_len]
        yield b1, payload, i, seg_len
        i += 2 + seg_len

# ═════════════════════════════════════════════════════════════════════════════
# SHARED: read star rating
# XnView MP writes real rating to XMP, leaves EXIF Rating tag at 0.
# So XMP wins over EXIF when EXIF is 0.
# ═════════════════════════════════════════════════════════════════════════════

def read_rating(path: Path) -> int:
    """Return star rating (0-5) from a JPEG file."""
    data = path.read_bytes()
    rating_exif = None
    rating_xmp  = None

    for b1, payload, _, _ in _iter_markers(data):

        # EXIF tag 0x4746 (Rating)
        if b1 == 0xE1 and payload[:6] == b"Exif\x00\x00":
            try:
                tiff = payload[6:]
                bo = "<" if tiff[:2] == b"II" else ">"
                ifd0_off = struct.unpack_from(bo + "I", tiff, 4)[0]
                n = struct.unpack_from(bo + "H", tiff, ifd0_off)[0]
                for e in range(min(n, 200)):
                    eoff = ifd0_off + 2 + e * 12
                    if eoff + 12 > len(tiff): break
                    tag, _, _, val = struct.unpack_from(bo + "HHII", tiff, eoff)
                    if tag == 0x4746:
                        rating_exif = val & 0xFFFF
            except Exception:
                pass

        # XMP element or attribute form
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
            except Exception:
                pass

    # XMP wins when EXIF is 0 (XnView behaviour)
    if rating_xmp is not None and rating_xmp != 0:
        rating = rating_xmp
    elif rating_exif is not None and rating_exif != 0:
        rating = rating_exif
    else:
        rating = 0

    logging.info("  %s  rating=%d  (xmp=%s  exif=%s)",
                 path.name, rating,
                 rating_xmp  if rating_xmp  is not None else "none",
                 rating_exif if rating_exif is not None else "none")
    return max(0, min(5, rating))

# ═════════════════════════════════════════════════════════════════════════════
# ROTATE MODE
# Approach (proven working via test_rotate_full.py):
#   1. Rotate pixels with Pillow -> save to memory buffer (clean JPEG)
#   2. Grab original XMP block, reset rating to 0 in it
#   3. Insert updated XMP right after SOI of the rotated output
#   4. Write to disk
# No marker reassembly, no surgery on image data.
# ═════════════════════════════════════════════════════════════════════════════

def rotate_file(path: Path) -> str:
    """
    Rotate JPEG by star rating and reset rating to 0.
    Returns 'rotated', 'skipped', or 'failed'.
    """
    rating = read_rating(path)

    if rating == 1:
        op, label = _ROT_LEFT,  "left (CCW)"
    elif rating == 2:
        op, label = _ROT_RIGHT, "right (CW)"
    else:
        return "skipped"

    logging.info("Rotate  %s  ->  %s", path.name, label)

    try:
        original_bytes = path.read_bytes()

        # Step 1: rotate pixels with Pillow, save to memory buffer
        img = Image.open(io.BytesIO(original_bytes))
        img.load()
        rotated = img.transpose(op)
        buf = io.BytesIO()
        rotated.save(buf, format="JPEG", quality=95, subsampling=0, optimize=True)
        rotated_bytes = buf.getvalue()

        # Step 2: grab XMP from original, reset rating to 0
        xmp_marker = None
        for b1, payload, offset, seg_len in _iter_markers(original_bytes):
            if b1 == 0xE1 and b"http://ns.adobe.com/xap" in payload[:64]:
                xmp_str = payload.decode("utf-8", errors="replace")
                xmp_str = re.sub(r"<xmp:Rating>\s*[-\d]+\s*</xmp:Rating>",
                                 "<xmp:Rating>0</xmp:Rating>", xmp_str)
                xmp_str = re.sub(r'xmp:Rating\s*=\s*"[-\d]*"',
                                 'xmp:Rating="0"', xmp_str)
                xmp_str = re.sub(r"xmp:Rating\s*=\s*'[-\d]*'",
                                 "xmp:Rating='0'", xmp_str)
                xmp_str = re.sub(
                    r"<MicrosoftPhoto:Rating>\s*\d+\s*</MicrosoftPhoto:Rating>",
                    "<MicrosoftPhoto:Rating>0</MicrosoftPhoto:Rating>", xmp_str)
                new_payload = xmp_str.encode("utf-8")
                new_len = len(new_payload) + 2
                xmp_marker = (bytes([0xFF, 0xE1,
                                     (new_len >> 8) & 0xFF, new_len & 0xFF])
                              + new_payload)
                break

        # Step 3: insert XMP right after SOI of the rotated output
        if xmp_marker is not None:
            final_bytes = rotated_bytes[:2] + xmp_marker + rotated_bytes[2:]
        else:
            final_bytes = rotated_bytes  # no XMP in original, just save rotated

        # Step 4: write to disk
        path.write_bytes(final_bytes)
        logging.info("  done - rating reset to 0")
        return "rotated"

    except Exception as exc:
        logging.error("  FAILED %s: %s", path.name, exc)
        return "failed"

# ═════════════════════════════════════════════════════════════════════════════
# CONVERT MODE  (unchanged - was working)
# ═════════════════════════════════════════════════════════════════════════════

_CANON_ORIENT_MAP = {0: 1, 1: 6, 2: 3, 3: 8}

def _canon_makernote_orientation(data: bytes):
    sig = b"Canon\x00"
    pos = data.find(sig)
    if pos == -1:
        return None
    for ifd_start in (pos + 6, pos + 8):
        try:
            val = _parse_ifd_tag(data, ifd_start, 0x0101)
            if val is not None:
                return _CANON_ORIENT_MAP.get(val)
        except Exception:
            pass
    return None

def _parse_ifd_tag(data: bytes, ifd_offset: int, target_tag: int):
    if ifd_offset + 2 > len(data):
        return None
    bo = "<"
    for i in range(ifd_offset, max(0, ifd_offset - 65536), -1):
        if data[i:i+2] == b"MM": bo = ">"; break
        if data[i:i+2] == b"II": bo = "<"; break
    n = struct.unpack_from(bo + "H", data, ifd_offset)[0]
    if not (0 < n < 512):
        return None
    for i in range(n):
        off = ifd_offset + 2 + i * 12
        if off + 12 > len(data): break
        tag, _, _, val = struct.unpack_from(bo + "HHII", data, off)
        if tag == target_tag:
            return val & 0xFFFF
    return None

def read_orientation(source: Path, raw) -> int:
    # exiftool (best for CR3)
    try:
        r = subprocess.run(
            ["exiftool", "-Orientation#", "-json", str(source)],
            capture_output=True, text=True, timeout=15,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
        if r.returncode == 0:
            import json
            d = json.loads(r.stdout)
            val = d[0].get("Orientation") if d else None
            if val is not None:
                logging.info("  Orientation (exiftool) = %d [%s]",
                             val, _ORIENT_DESC.get(val, "?"))
                return int(val)
    except FileNotFoundError:
        logging.debug("  exiftool not found (optional, helps with CR3)")
    except Exception:
        pass

    # Canon makernote
    if source.suffix.lower() in {".cr2", ".cr3"}:
        val = _canon_makernote_orientation(source.read_bytes())
        if val is not None:
            logging.info("  Orientation (Canon makernote) = %d [%s]",
                         val, _ORIENT_DESC.get(val, "?"))
            return val

    # rawpy flip
    try:
        flip = raw.sizes.flip
        val  = {0: 1, 3: 3, 5: 6, 6: 8}.get(flip, 1)
        if val != 1:
            logging.info("  Orientation (rawpy flip=%d) = %d", flip, val)
            return val
    except Exception:
        pass

    # piexif
    if _HAS_PIEXIF:
        try:
            d   = piexif.load(str(source))
            val = d.get("0th", {}).get(piexif.ImageIFD.Orientation)
            if val and val != 1:
                logging.info("  Orientation (piexif) = %d", val)
                return val
        except Exception:
            pass

    return 1

def colour_adjust(img, cfg):
    c = cfg.get("colour", {})
    for attr, cls in [("brightness", ImageEnhance.Brightness),
                      ("contrast",   ImageEnhance.Contrast),
                      ("saturation", ImageEnhance.Color)]:
        v = float(c.get(attr, 1.0))
        if v != 1.0:
            img = cls(img).enhance(v)
    sharp = int(c.get("sharpening", 1))
    if sharp == 1:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=80, threshold=3))
    elif sharp >= 2:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.5, percent=130, threshold=3))
    return img

def output_path(source: Path, cfg) -> Path:
    d = cfg.get("output", {}).get("directory", "").strip()
    if d:
        base = Path(d)
        base.mkdir(parents=True, exist_ok=True)
        return base / (source.stem + ".jpg")
    return source.with_suffix(".jpg")

def convert_file(source: Path, cfg) -> str:
    dest = output_path(source, cfg)
    if dest.exists():
        logging.info("SKIP  %s  (already exists)", source.name)
        return "skipped"

    logging.info("Convert  %s", source.name)
    jcfg = cfg.get("jpeg", {})

    try:
        with rawpy.imread(str(source)) as raw:
            orientation = read_orientation(source, raw)
            rgb = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=True,
                output_bps=8,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AAHD,
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Light,
                output_color=rawpy.ColorSpace.sRGB,
            )
            img = Image.fromarray(rgb)
            logging.info("  %dx%d px", img.width, img.height)

            op = _ORIENT_OP.get(orientation)
            if op:
                img = img.transpose(op)
                logging.info("  rotated orientation=%d -> %dx%d",
                             orientation, img.width, img.height)

            img = colour_adjust(img, cfg)

            save_kw = {
                "quality":     int(jcfg.get("quality", 95)),
                "subsampling": int(jcfg.get("subsampling", 0)),
                "optimize":    bool(jcfg.get("optimize", True)),
            }
            if jcfg.get("embed_icc_profile", True):
                try:
                    pb = raw.color_profile
                    if pb: save_kw["icc_profile"] = pb
                except AttributeError:
                    pass

            img.save(str(dest), format="JPEG", **save_kw)

        kb = dest.stat().st_size // 1024
        logging.info("  done -> %s (%d KB)", dest.name, kb)
        return "converted"

    except Exception as exc:
        logging.error("  FAILED %s: %s", source.name, exc)
        return "failed"

# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

def iter_files(target: Path, extensions: set):
    if target.is_file():
        yield target
    else:
        for p in sorted(target.rglob("*")):
            if p.is_file() and p.suffix.lower() in extensions:
                yield p

def build_parser():
    p = argparse.ArgumentParser(
        prog="raw2jpg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="RAW->JPG converter and JPEG rotation tool.",
        epilog="""
examples:
  python raw2jpg.py -c -f photo.cr2
  python raw2jpg.py -c -d C:\\shoot
  python raw2jpg.py -r -f photo.jpg
  python raw2jpg.py -r -d C:\\shoot\\converted
        """)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("-c", action="store_true", help="Convert RAW to JPEG")
    mode.add_argument("-r", action="store_true", help="Rotate JPEG by star rating")
    tgt = p.add_mutually_exclusive_group(required=True)
    tgt.add_argument("-f", metavar="FILE", help="Single file")
    tgt.add_argument("-d", metavar="DIR",  help="Directory (recursive)")
    p.add_argument("--config", metavar="CONFIG", default=None)
    return p

def main():
    args = build_parser().parse_args()
    cfg  = load_config(args.config)
    setup_logging(cfg)

    target = Path(args.f or args.d)
    if not target.exists():
        logging.error("Not found: %s", target)
        sys.exit(1)

    if args.c:
        files = list(iter_files(target, RAW_EXTENSIONS))
        if not files:
            logging.warning("No RAW files found"); sys.exit(0)
        logging.info("Found %d RAW file(s)", len(files))
        counts = {"converted": 0, "skipped": 0, "failed": 0}
        for f in files:
            counts[convert_file(f, cfg)] += 1
        logging.info("Done  converted=%d  skipped=%d  failed=%d",
                     counts["converted"], counts["skipped"], counts["failed"])

    elif args.r:
        files = list(iter_files(target, {".jpg", ".jpeg"}))
        if not files:
            logging.warning("No JPEG files found"); sys.exit(0)
        logging.info("Found %d JPEG file(s)", len(files))
        counts = {"rotated": 0, "skipped": 0, "failed": 0}
        for f in files:
            counts[rotate_file(f)] += 1
        logging.info("Done  rotated=%d  skipped=%d  failed=%d",
                     counts["rotated"], counts["skipped"], counts["failed"])

if __name__ == "__main__":
    main()