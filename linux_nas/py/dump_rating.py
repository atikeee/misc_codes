#!/usr/bin/env python3
"""
raw2jpg.py  –  RAW → JPG converter + JPEG rotation tool

MODES
-----
  -c   Convert mode  : convert RAW files to JPEG
  -r   Rotate mode   : rotate JPEGs based on their star rating, then clear the rating
                         ★ (1 star) → rotate 90° counter-clockwise (left)
                         ★★(2 stars) → rotate 90° clockwise (right)

TARGET
------
  -f FILE        single file
  -d DIRECTORY   all matching files, recursively

EXAMPLES
--------
  python raw2jpg.py -c -f photo.cr2
  python raw2jpg.py -c -d C:\\shoot
  python raw2jpg.py -c -d C:\\shoot --config studio.yaml
  python raw2jpg.py -r -d C:\\shoot\\converted

DEPENDENCIES
------------
  pip install rawpy pillow pyyaml piexif
  Optional but recommended for CR3:  exiftool  (https://exiftool.org)
"""

from __future__ import annotations

import argparse
import logging
import struct
import subprocess
import sys
from pathlib import Path

# ── dependency check ──────────────────────────────────────────────────────────

def _require(package: str, pip_name: str | None = None):
    import importlib
    try:
        return importlib.import_module(package)
    except ImportError:
        print(f"[ERROR] '{package}' not installed.  Run: pip install {pip_name or package}",
              file=sys.stderr)
        sys.exit(1)

_require("rawpy");  _require("yaml", "pyyaml");  _require("PIL", "pillow")

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

# EXIF Orientation (0x0112) → Pillow Transpose operation
try:
    _T = Image.Transpose
    _ORIENT_OP = {
        2: _T.FLIP_LEFT_RIGHT,
        3: _T.ROTATE_180,
        4: _T.FLIP_TOP_BOTTOM,
        5: _T.TRANSPOSE,
        6: _T.ROTATE_270,   # shot CW  → correct CCW
        7: _T.TRANSVERSE,
        8: _T.ROTATE_90,    # shot CCW → correct CW
    }
    _ROT_LEFT  = _T.ROTATE_90    # 90° CCW
    _ROT_RIGHT = _T.ROTATE_270   # 90° CW
except AttributeError:           # Pillow < 9.1 fallback
    _ORIENT_OP = {
        2: Image.FLIP_LEFT_RIGHT, 3: Image.ROTATE_180, 4: Image.FLIP_TOP_BOTTOM,
        5: Image.TRANSPOSE, 6: Image.ROTATE_270, 7: Image.TRANSVERSE, 8: Image.ROTATE_90,
    }
    _ROT_LEFT  = Image.ROTATE_90
    _ROT_RIGHT = Image.ROTATE_270

_ORIENT_DESC = {
    1: "Normal", 2: "Flip H", 3: "180°", 4: "Flip V",
    5: "90°CW+flip", 6: "90°CW", 7: "90°CCW+flip", 8: "90°CCW",
}

# XMP rating tag id (used in JPEG APP1 XMP block)
_XMP_RATING_TAG = "xmp:Rating"

# ── default config ────────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict = {
    "output": {
        "directory": "",          # "" = same folder as source
    },
    "jpeg": {
        "quality":           95,
        "subsampling":        0,  # 0=4:4:4  1=4:2:2  2=4:2:0
        "optimize":        True,
        "embed_icc_profile": True,
    },
    "colour": {
        "brightness":  1.0,
        "contrast":    1.0,
        "saturation":  1.0,
        "sharpening":    1,       # 0=off  1=mild  2=stronger
    },
    "logging": {
        "level":    "INFO",
        "log_file": "conversion.log",
    },
}

# ── config helpers ────────────────────────────────────────────────────────────

def _merge(base: dict, over: dict) -> dict:
    result = dict(base)
    for k, v in over.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: str | None) -> dict:
    if path is None:
        candidate = Path(__file__).with_name("config.yaml")
        path = str(candidate) if candidate.exists() else None
    if path is None:
        print("[CONFIG] Using built-in defaults (no config.yaml found)", flush=True)
        return DEFAULT_CONFIG
    print(f"[CONFIG] {path}", flush=True)
    with open(path, encoding="utf-8") as fh:
        user = yaml.safe_load(fh) or {}
    cfg = _merge(DEFAULT_CONFIG, user)
    print(f"[CONFIG] output.directory = '{cfg['output']['directory']}' "
          f"(empty = same folder as source)", flush=True)
    return cfg


def setup_logging(cfg: dict) -> None:
    lc  = cfg.get("logging", {})
    lvl = getattr(logging, lc.get("level", "INFO").upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if lc.get("log_file"):
        handlers.append(logging.FileHandler(lc["log_file"], encoding="utf-8"))
    logging.basicConfig(level=lvl,
                        format="%(asctime)s  %(levelname)-8s  %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                        handlers=handlers)

# ══════════════════════════════════════════════════════════════════════════════
# CONVERT MODE
# ══════════════════════════════════════════════════════════════════════════════

# ── Canon makernote orientation ───────────────────────────────────────────────

_CANON_ORIENT_MAP = {0: 1, 1: 6, 2: 3, 3: 8}   # CameraOrientation → EXIF


def _canon_makernote_orientation(data: bytes) -> int | None:
    """Scan file bytes for the Canon makernote and read CameraOrientation (0x0101)."""
    sig = b"Canon\x00"
    pos = data.find(sig)
    if pos == -1:
        return None
    for ifd_start in (pos + 6, pos + 8):
        try:
            val = _parse_ifd_tag(data, ifd_start, 0x0101)
            if val is not None:
                exif = _CANON_ORIENT_MAP.get(val)
                logging.debug("  Canon makernote CameraOrientation=%d → EXIF %s", val, exif)
                return exif
        except Exception:
            pass
    return None


def _parse_ifd_tag(data: bytes, ifd_offset: int, target_tag: int) -> int | None:
    """Parse a TIFF IFD at *ifd_offset* and return the value of *target_tag*."""
    if ifd_offset + 2 > len(data):
        return None
    # detect byte order
    bo = "<"
    for i in range(ifd_offset, max(0, ifd_offset - 65536), -1):
        if data[i:i+2] == b"MM": bo = ">"; break
        if data[i:i+2] == b"II": bo = "<"; break
    n = struct.unpack_from(bo + "H", data, ifd_offset)[0]
    if not (0 < n < 512):
        return None
    for i in range(n):
        off = ifd_offset + 2 + i * 12
        if off + 12 > len(data):
            break
        tag, _, _, val = struct.unpack_from(bo + "HHII", data, off)
        if tag == target_tag:
            return val & 0xFFFF
    return None


# ── EXIF orientation reader ───────────────────────────────────────────────────

def read_orientation(source: Path, raw: rawpy.RawPy) -> int:
    """
    Return the EXIF Orientation (1–8) for *source*.
    Tries (in order): exiftool → Canon makernote → rawpy flip → piexif.
    Returns 1 (no rotation) if nothing is found.
    """
    # exiftool (most reliable for CR3)
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
                logging.info("  Orientation (exiftool) = %d  [%s]",
                             val, _ORIENT_DESC.get(val, "?"))
                return int(val)
    except FileNotFoundError:
        logging.debug("  exiftool not on PATH (install from exiftool.org for best CR3 support)")
    except Exception:
        pass

    # Canon makernote binary parse
    if source.suffix.lower() in {".cr2", ".cr3"}:
        val = _canon_makernote_orientation(source.read_bytes())
        if val is not None:
            logging.info("  Orientation (Canon makernote) = %d  [%s]",
                         val, _ORIENT_DESC.get(val, "?"))
            return val

    # rawpy sizes.flip
    flip_map = {0: 1, 3: 3, 5: 6, 6: 8}
    try:
        flip = raw.sizes.flip
        val  = flip_map.get(flip, 1)
        logging.info("  Orientation (rawpy flip=%d) = %d  [%s]",
                     flip, val, _ORIENT_DESC.get(val, "?"))
        if val != 1:
            return val
    except Exception:
        pass

    # piexif
    if _HAS_PIEXIF:
        try:
            d   = piexif.load(str(source))
            val = d.get("0th", {}).get(piexif.ImageIFD.Orientation)
            if val:
                logging.info("  Orientation (piexif) = %d  [%s]",
                             val, _ORIENT_DESC.get(val, "?"))
                return val
        except Exception:
            pass

    logging.warning("  Orientation not found – assuming upright (no rotation)")
    return 1


# ── colour adjustments ────────────────────────────────────────────────────────

def colour_adjust(img: Image.Image, cfg: dict) -> Image.Image:
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


# ── output path ───────────────────────────────────────────────────────────────

def output_path(source: Path, cfg: dict) -> Path:
    d = cfg.get("output", {}).get("directory", "").strip()
    if d:
        base = Path(d)
        base.mkdir(parents=True, exist_ok=True)
        return base / (source.stem + ".jpg")
    return source.with_suffix(".jpg")


# ── single file convert ───────────────────────────────────────────────────────

def convert_file(source: Path, cfg: dict) -> str:
    """Returns 'converted', 'skipped', or 'failed'."""
    dest = output_path(source, cfg)
    if dest.exists():
        logging.info("SKIP  %s  (already exists)", source.name)
        return "skipped"

    logging.info("Convert  %s  →  %s", source.name, dest)
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
            logging.info("  Demosaiced: %d×%d px", img.width, img.height)

            # apply orientation correction
            op = _ORIENT_OP.get(orientation)
            if op:
                img = img.transpose(op)
                logging.info("  Rotated: orientation %d → %d×%d px",
                             orientation, img.width, img.height)

            img = colour_adjust(img, cfg)

            save_kw: dict = {
                "quality":     int(jcfg.get("quality", 95)),
                "subsampling": int(jcfg.get("subsampling", 0)),
                "optimize":    bool(jcfg.get("optimize", True)),
            }
            if jcfg.get("embed_icc_profile", True):
                try:
                    pb = raw.color_profile
                    if pb:
                        save_kw["icc_profile"] = pb
                except AttributeError:
                    pass

            img.save(str(dest), format="JPEG", **save_kw)

        kb = dest.stat().st_size // 1024
        logging.info("  ✓  %s  (%d KB)", dest.name, kb)
        return "converted"

    except Exception as exc:
        logging.error("  ✗  %s: %s", source.name, exc)
        return "failed"


# ══════════════════════════════════════════════════════════════════════════════
# ROTATE MODE  (JPEG only, driven by XMP star rating)
# ══════════════════════════════════════════════════════════════════════════════

def read_rating(path: Path) -> int:
    """
    Read the star rating from a JPEG file.

    Checks every location apps use to store ratings:
      1. EXIF IFD0 tag 0x4746  (Rating, 0-5 direct)
         EXIF IFD0 tag 0x4749  (RatingPercent: 1/25/50/75/99 -> 1-5 stars)
      2. XMP element:   <xmp:Rating>2</xmp:Rating>
         XMP attribute: xmp:Rating="2"
      3. XMP MicrosoftPhoto:Rating (percent fallback)

    Key fix: scans ALL JPEG markers, not just APPn (0xE0-0xEF).
    XnView MP places the XMP APP1 AFTER the DQT (0xFFDB) marker so the
    old loop that stopped at non-APP markers missed it completely.
    """
    import re, struct

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
            # markers without a length field
            if b1 in (0xD8, 0xD9, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7):
                i += 2
                continue
            # SOS = compressed image data begins, stop here
            if b1 == 0xDA:
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
        logging.debug("  read_rating error %s: %s", path.name, exc)

    if rating_exif is not None:
        rating = rating_exif
    elif rating_xmp is not None:
        rating = rating_xmp
    else:
        rating = 0
    rating = max(0, min(5, rating))

    logging.info("  Rating  %s  ->  exif=%s  xmp=%s  using=%d",
                 path.name,
                 str(rating_exif) if rating_exif is not None else "none",
                 str(rating_xmp)  if rating_xmp  is not None else "none",
                 rating)
    return rating

def rotate_file(path: Path) -> str:
    """
    1. Read XMP rating from the JPEG.
    2. rating == 1 -> rotate left (CCW 90deg).
       rating == 2 -> rotate right (CW 90deg).
       Any other value (0, 3-5) -> skip, do NOT touch the file.
    3. Save rotated pixels back, preserving ALL original APP markers
       (EXIF, XMP, ICC profile ...) so nothing is lost.
    4. In the same write, set xmp:Rating to 0 in the XMP block.
    Returns 'rotated', 'skipped', or 'failed'.
    """
    import io, re

    rating = read_rating(path)

    if rating == 1:
        op    = _ROT_LEFT
        label = "left (CCW)"
    elif rating == 2:
        op    = _ROT_RIGHT
        label = "right (CW)"
    else:
        if rating != 0:
            logging.info("SKIP  %s  (rating=%d – only 1 or 2 trigger rotation)",
                         path.name, rating)
        return "skipped"

    logging.info("Rotate  %s  rating=%d  %s", path.name, rating, label)

    try:
        original_bytes = path.read_bytes()

        # ── Step 1: rotate pixel data via Pillow ─────────────────────────────
        img = Image.open(io.BytesIO(original_bytes))
        img.load()

        # Clear EXIF Orientation tag so viewers won't double-rotate
        exif_bytes = img.info.get("exif", b"")
        if exif_bytes and _HAS_PIEXIF:
            try:
                ed = piexif.load(exif_bytes)
                ed["0th"].pop(piexif.ImageIFD.Orientation, None)
                exif_bytes = piexif.dump(ed)
            except Exception:
                pass

        rotated = img.transpose(op)

        buf = io.BytesIO()
        save_kw: dict = {"format": "JPEG", "quality": 95,
                         "subsampling": 0, "optimize": True}
        if exif_bytes:
            save_kw["exif"] = exif_bytes
        rotated.save(buf, **save_kw)
        rotated_bytes = buf.getvalue()

        # ── Step 2: collect original APP markers (skip EXIF, capture XMP) ────
        # Pillow drops XMP, ICC, IPTC etc.  We re-attach them manually.
        orig_xmp: bytes | None = None
        extra_apps: list[bytes] = []   # ICC profile, IPTC, any other APPn

        i = 2  # skip SOI
        while i + 3 < len(original_bytes):
            b0, b1 = original_bytes[i], original_bytes[i + 1]
            if b0 != 0xFF or b1 < 0xE0:
                break  # past the APP section
            seg_len = (original_bytes[i + 2] << 8) | original_bytes[i + 3]
            marker_bytes = original_bytes[i: i + 2 + seg_len]
            payload      = original_bytes[i + 4: i + 2 + seg_len]

            is_exif = payload[:6] == b"Exif\x00\x00"
            is_xmp  = b"http://ns.adobe.com/xap" in payload[:64]

            if is_xmp:
                orig_xmp = marker_bytes
            elif not is_exif:
                extra_apps.append(marker_bytes)

            i += 2 + seg_len

        # ── Step 3: rebuild XMP with rating = 0 ──────────────────────────────
        if orig_xmp is not None:
            xmp_str = orig_xmp[4:].decode("utf-8", errors="replace")
            # attribute form:  xmp:Rating="N"
            new_xmp_str = re.sub(
                r'xmp:Rating\s*=\s*["\'][^"\']*["\']',
                'xmp:Rating="0"', xmp_str)
            # element form: <xmp:Rating>N</xmp:Rating>
            new_xmp_str = re.sub(
                r'<xmp:Rating>\s*\d+\s*</xmp:Rating>',
                '<xmp:Rating>0</xmp:Rating>', new_xmp_str)
            new_payload = new_xmp_str.encode("utf-8")
            new_len = len(new_payload) + 2
            xmp_app1 = (bytes([0xFF, 0xE1, (new_len >> 8) & 0xFF, new_len & 0xFF])
                        + new_payload)
        else:
            # No XMP existed – inject a minimal block with rating=0
            payload = (
                b"http://ns.adobe.com/xap/1.0/"
                + b"\x00"
                + b'<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?>'
                + b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                + b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                + b'<rdf:Description rdf:about=""'
                + b' xmlns:xmp="http://ns.adobe.com/xap/1.0/"'
                + b' xmp:Rating="0"/>'
                + b"</rdf:RDF></x:xmpmeta>"
                + b'<?xpacket end="w"?>'
            )
            new_len = len(payload) + 2
            xmp_app1 = (bytes([0xFF, 0xE1, (new_len >> 8) & 0xFF, new_len & 0xFF])
                        + payload)

        # ── Step 4: find where Pillow's APP section ends in rotated output ────
        j = 2
        while j + 3 < len(rotated_bytes):
            b0, b1 = rotated_bytes[j], rotated_bytes[j + 1]
            if b0 != 0xFF or b1 < 0xE0:
                break
            seg_len = (rotated_bytes[j + 2] << 8) | rotated_bytes[j + 3]
            j += 2 + seg_len
        # j now points at DQT / SOF / first non-APP marker
        pillow_apps = rotated_bytes[2:j]   # EXIF written by Pillow
        image_data  = rotated_bytes[j:]    # quantisation tables, scan data, EOI

        # ── Step 5: assemble final JPEG ───────────────────────────────────────
        final = (
            b"\xFF\xD8"           # SOI
            + pillow_apps         # Pillow's EXIF APP1 (orientation cleared)
            + xmp_app1            # XMP APP1 with rating=0
            + b"".join(extra_apps)# ICC profile / IPTC / other APPs
            + image_data          # DQT, SOF0, SOS, scan, EOI
        )

        path.write_bytes(final)
        logging.info("  rating reset to 0, saved %s", path.name)
        return "rotated"

    except Exception as exc:
        logging.error("  FAILED %s: %s", path.name, exc)
        return "failed"



# ── file discovery ────────────────────────────────────────────────────────────

def iter_files(target: Path, extensions: set[str]):
    if target.is_file():
        yield target
    else:
        for p in sorted(target.rglob("*")):
            if p.is_file() and p.suffix.lower() in extensions:
                yield p


# ── CLI ───────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="raw2jpg",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="RAW → JPG converter and JPEG rotation tool.",
        epilog="""
MODES
  -c  Convert RAW files to JPEG
  -r  Rotate JPEGs by star rating (★=left  ★★=right), then reset rating to 0

EXAMPLES
  python raw2jpg.py -c -f photo.cr2
  python raw2jpg.py -c -d C:\\shoot
  python raw2jpg.py -r -d C:\\shoot\\converted
        """,
    )
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("-c", action="store_true", help="Convert mode (RAW → JPEG)")
    mode.add_argument("-r", action="store_true", help="Rotate mode  (JPEG by rating)")

    target = p.add_mutually_exclusive_group(required=True)
    target.add_argument("-f", metavar="FILE", help="Single file")
    target.add_argument("-d", metavar="DIR",  help="Directory (recursive)")

    p.add_argument("--config", metavar="CONFIG", default=None,
                   help="YAML config file (default: config.yaml next to script)")
    return p


def main() -> None:
    args = build_parser().parse_args()
    cfg  = load_config(args.config)
    setup_logging(cfg)

    target = Path(args.f or args.d)
    if not target.exists():
        logging.error("Not found: %s", target)
        sys.exit(1)

    # ── CONVERT mode ──────────────────────────────────────────────────────────
    if args.c:
        files = list(iter_files(target, RAW_EXTENSIONS))
        if not files:
            logging.warning("No RAW files found under %s", target)
            sys.exit(0)
        logging.info("Found %d RAW file(s)", len(files))
        counts: dict[str, int] = {"converted": 0, "skipped": 0, "failed": 0}
        for f in files:
            counts[convert_file(f, cfg)] += 1
        logging.info("")
        logging.info("Done  converted=%d  skipped=%d  failed=%d",
                     counts["converted"], counts["skipped"], counts["failed"])

    # ── ROTATE mode ───────────────────────────────────────────────────────────
    elif args.r:
        files = list(iter_files(target, {".jpg", ".jpeg"}))
        if not files:
            logging.warning("No JPEG files found under %s", target)
            sys.exit(0)
        logging.info("Found %d JPEG file(s)", len(files))
        counts = {"rotated": 0, "skipped": 0, "failed": 0}
        for f in files:
            counts[rotate_file(f)] += 1
        logging.info("")
        logging.info("Done  rotated=%d  skipped=%d  failed=%d",
                     counts["rotated"], counts["skipped"], counts["failed"])


if __name__ == "__main__":
    main()