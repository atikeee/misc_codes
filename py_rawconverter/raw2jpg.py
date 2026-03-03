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

def read_xmp_rating(path: Path) -> int:
    """
    Read the XMP Rating from a JPEG file.
    Returns an integer (typically 0–5) or 0 if not found.

    The XMP block is embedded in JPEG APP1 markers alongside EXIF.
    It looks like:  <?xpacket ...><x:xmpmeta ...><rdf:RDF>
                      <rdf:Description xmp:Rating="2" .../>
                    </rdf:RDF></x:xmpmeta>
    """
    import re
    try:
        data = path.read_bytes()
        # Scan JPEG APP1 markers (0xFFE1)
        i = 2  # skip SOI
        while i < len(data) - 4:
            marker = (data[i] << 8) | data[i + 1]
            length = (data[i + 2] << 8) | data[i + 3]
            if marker == 0xFFE1:
                chunk = data[i + 4: i + 2 + length]
                if b"http://ns.adobe.com/xap" in chunk:
                    xmp_str = chunk.decode("utf-8", errors="replace")
                    # Try attribute form first: xmp:Rating="2"
                    m = re.search(r'xmp:Rating\s*=\s*["\'](\d+)["\']', xmp_str)
                    if m:
                        return int(m.group(1))
                    # Try element form: <xmp:Rating>2</xmp:Rating>
                    m = re.search(r'<xmp:Rating>\s*(\d+)\s*</xmp:Rating>', xmp_str)
                    if m:
                        return int(m.group(1))
            i += 2 + length
    except Exception as exc:
        logging.debug("  read_xmp_rating %s: %s", path.name, exc)
    return 0


def write_xmp_rating(path: Path, rating: int) -> bool:
    """
    Write (or update) the xmp:Rating value inside the JPEG's XMP block.
    If no XMP block exists, injects a minimal one.
    Returns True on success.
    """
    import re
    try:
        data = path.read_bytes()
        i = 2
        xmp_start = xmp_end = -1
        while i < len(data) - 4:
            marker = (data[i] << 8) | data[i + 1]
            length = (data[i + 2] << 8) | data[i + 3]
            if marker == 0xFFE1:
                chunk = data[i + 4: i + 2 + length]
                if b"http://ns.adobe.com/xap" in chunk:
                    xmp_start = i
                    xmp_end   = i + 2 + length
                    break
            i += 2 + length

        rating_str = str(rating)

        if xmp_start == -1:
            # No XMP block – inject a minimal one after the SOI marker
            xmp_payload = (
                'http://ns.adobe.com/xap/1.0/\x00'
                '<?xpacket begin="\xef\xbb\xbf" id="W5M0MpCehiHzreSzNTczkc9d"?>'
                '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
                '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
                f'<rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="{rating_str}"/>'
                '</rdf:RDF></x:xmpmeta>'
                '<?xpacket end="w"?>'
            ).encode("utf-8")
            length_field = len(xmp_payload) + 2
            app1 = bytes([0xFF, 0xE1,
                          (length_field >> 8) & 0xFF,
                          length_field & 0xFF]) + xmp_payload
            new_data = data[:2] + app1 + data[2:]
        else:
            chunk = data[xmp_start + 4: xmp_end]
            xmp_str = chunk.decode("utf-8", errors="replace")

            # Replace existing rating (attribute or element form)
            new_xmp = re.sub(r'xmp:Rating\s*=\s*["\'][^"\']*["\']',
                             f'xmp:Rating="{rating_str}"', xmp_str)
            if new_xmp == xmp_str:  # attribute not found, try element form
                new_xmp = re.sub(r'<xmp:Rating>\s*\d+\s*</xmp:Rating>',
                                 f'<xmp:Rating>{rating_str}</xmp:Rating>', xmp_str)
            if new_xmp == xmp_str:  # neither found – add attribute to rdf:Description
                new_xmp = re.sub(
                    r'(<rdf:Description\b[^/]*/?>)',
                    lambda m: m.group(1).replace(">", f' xmp:Rating="{rating_str}">', 1)
                              if "/>" not in m.group(1)
                              else m.group(1).replace("/>", f' xmp:Rating="{rating_str}"/>', 1),
                    xmp_str, count=1)

            new_chunk   = new_xmp.encode("utf-8")
            new_length  = len(new_chunk) + 2
            new_data = (data[:xmp_start]
                        + bytes([0xFF, 0xE1, (new_length >> 8) & 0xFF, new_length & 0xFF])
                        + new_chunk
                        + data[xmp_end:])

        path.write_bytes(new_data)
        return True

    except Exception as exc:
        logging.error("  write_xmp_rating %s: %s", path.name, exc)
        return False


def rotate_jpeg_lossless(path: Path, op) -> bool:
    """
    Rotate a JPEG losslessly using Pillow transpose and re-save at max quality.
    We preserve the original EXIF (minus the Orientation tag which we clear).
    """
    try:
        img = Image.open(str(path))
        img.load()

        # grab existing exif and clear orientation tag so viewer doesn't re-rotate
        exif_bytes = img.info.get("exif", b"")
        if exif_bytes and _HAS_PIEXIF:
            try:
                ed = piexif.load(exif_bytes)
                ed["0th"].pop(piexif.ImageIFD.Orientation, None)
                exif_bytes = piexif.dump(ed)
            except Exception:
                pass

        rotated = img.transpose(op)

        save_kw: dict = {"format": "JPEG", "quality": 95,
                         "subsampling": 0, "optimize": True}
        if exif_bytes:
            save_kw["exif"] = exif_bytes

        rotated.save(str(path), **save_kw)
        return True
    except Exception as exc:
        logging.error("  rotate failed %s: %s", path.name, exc)
        return False


def rotate_file(path: Path) -> str:
    """
    Read XMP rating, rotate accordingly, reset rating to 0.
    Returns 'rotated', 'skipped', or 'failed'.
    """
    rating = read_xmp_rating(path)

    if rating == 0:
        logging.debug("SKIP  %s  (rating=0, no rotation needed)", path.name)
        return "skipped"

    if rating == 1:
        op    = _ROT_LEFT
        label = "← left (CCW)"
    elif rating == 2:
        op    = _ROT_RIGHT
        label = "→ right (CW)"
    else:
        logging.info("SKIP  %s  (rating=%d, only 1/2 trigger rotation)", path.name, rating)
        return "skipped"

    logging.info("Rotate  %s  rating=%d  %s", path.name, rating, label)

    if not rotate_jpeg_lossless(path, op):
        return "failed"

    # Reset rating to 0
    if not write_xmp_rating(path, 0):
        logging.warning("  ⚠  Rotation OK but could not clear rating for %s", path.name)

    logging.info("  ✓  %s rotated %s, rating reset to 0", path.name, label)
    return "rotated"


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