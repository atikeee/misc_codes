#!/usr/bin/env python3
"""
yt_download.py — Download YouTube/Facebook videos from a text file

Usage:
    python yt_download.py <input_file> [options]

Text file format:
    - One URL per line
    - Lines starting with # are ignored (comments)
    - Empty lines are ignored
    - Supports optional per-line sections:  URL *00:01:00-00:03:00
"""

import argparse
import os
import shutil
import subprocess
import sys
import re
from pathlib import Path

# --- ANSI Colors --------------------------------------------------------------
class Colors:
    RED    = "\033[0;31m"
    GREEN  = "\033[0;32m"
    YELLOW = "\033[1;33m"
    CYAN   = "\033[0;36m"
    BOLD   = "\033[1m"
    NC     = "\033[0m"  # Reset

def c(color: str, text: str) -> str:
    """Wrap text in an ANSI color code."""
    return f"{color}{text}{Colors.NC}"

# --- Defaults -----------------------------------------------------------------
DEFAULT_FORMAT      = "mp4"
DEFAULT_LINKS_FILE  = "yt-dld-links.txt"
DEFAULT_QUALITY     = "0"
DEFAULT_OUTPUT_DIR  = "/media/youtube"
DEFAULT_COOKIE_FILE = "yt_dld_cookies.txt"

SUPPORTED_DOMAINS = re.compile(
    r"(youtube\.com|youtu\.be|fb\.com|facebook\.com|fb\.watch|share/r)"
)

# --- Argument Parsing ---------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="yt_download.py",
        description="Batch download YouTube/Facebook videos.",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            "Input file example:\n"
            "  # My playlist\n"
            "  https://www.youtube.com/watch?v=abc123\n"
            "  https://youtu.be/xyz456  *00:01:00-00:03:00\n"
        ),
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        default=DEFAULT_LINKS_FILE,
        help=f"Text file with URLs (default: {DEFAULT_LINKS_FILE})",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["mp4", "mp3"],
        default=DEFAULT_FORMAT,
        help="Output format: mp4 or mp3 (default: mp4)",
    )
    parser.add_argument(
        "-o", "--output",
        default=DEFAULT_OUTPUT_DIR,
        dest="output_dir",
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "-s", "--section",
        default="",
        help="Global time range to trim, e.g. *00:01:00-00:03:00",
    )
    parser.add_argument(
        "-t", "--tempo",
        default="",
        dest="slow_tempo",
        help="Slow-down speed for mp3, e.g. 0.75",
    )
    parser.add_argument(
        "-d", "--dry-run",
        action="store_true",
        help="Preview commands without downloading",
    )
    parser.add_argument(
        "-c", "--cookies",
        default=DEFAULT_COOKIE_FILE,
        dest="cookie_file",
        help=f"Netscape cookie file (default: {DEFAULT_COOKIE_FILE})",
    )
    return parser.parse_args()

# --- Validation ---------------------------------------------------------------
def check_dependencies() -> None:
    if not shutil.which("yt-dlp"):
        print(c(Colors.RED, "Error: yt-dlp not found. Install it first:"))
        print(
            "  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
            " -o /usr/local/bin/yt-dlp"
        )
        print("  chmod a+rx /usr/local/bin/yt-dlp")
        sys.exit(1)

    if not shutil.which("ffmpeg"):
        print(c(Colors.YELLOW, "Warning: ffmpeg not found — audio extraction and trimming won't work."))

# --- Build yt-dlp command -----------------------------------------------------
def build_command(
    url: str,
    output_dir: str,
    fmt: str,
    quality: str,
    active_section: str,
    slow_tempo: str,
    cookie_file: str,
) -> list[str]:
    output_template = os.path.join(output_dir, "%(title).80s [%(id)s].%(ext)s")

    cmd = [
        "yt-dlp",
        "-o", output_template,
        "--user-agent", "facebookexternalhit/1.1",
    ]

    if os.path.isfile(cookie_file):
        cmd += ["--cookies", cookie_file]

    if fmt == "mp3":
        cmd += [
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", quality,
        ]
        if slow_tempo:
            cmd += ["--postprocessor-args", f"ffmpeg:-filter:a atempo={slow_tempo}"]
    else:
        cmd += [
            "-f",
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=1080]+bestaudio/best[ext=mp4]/best",
            "--merge-output-format", "mp4",
        ]

    if active_section:
        cmd += ["--download-sections", active_section]

    cmd.append(url)
    return cmd

# --- Process URLs -------------------------------------------------------------
def process_urls(args: argparse.Namespace) -> None:
    input_file   = args.input_file
    output_dir   = args.output_dir
    fmt          = args.format
    global_sect  = args.section
    slow_tempo   = args.slow_tempo
    dry_run      = args.dry_run
    cookie_file  = args.cookie_file

    if not os.path.isfile(input_file):
        print(c(Colors.RED, f"Error: File not found — {input_file}"))
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # --- Header ---------------------------------------------------------------
    print(c(Colors.CYAN, "=" * 40))
    print(c(Colors.CYAN, "  YouTube Batch Downloader"))
    print(c(Colors.CYAN, "=" * 40))
    print(f"  File:    {c(Colors.BOLD, input_file)}")
    print(f"  Format:  {c(Colors.BOLD, fmt)}")
    print(f"  Output:  {c(Colors.BOLD, output_dir)}")
    if global_sect:
        print(f"  Section: {c(Colors.BOLD, global_sect)}")
    if slow_tempo:
        print(f"  Tempo:   {c(Colors.BOLD, slow_tempo)}")
    if dry_run:
        print(c(Colors.YELLOW, "  [DRY RUN — no downloads]"))
    print()

    # --- Counters -------------------------------------------------------------
    total       = 0
    success     = 0
    failed      = 0
    skipped     = 0
    failed_urls: list[str] = []

    # --- Read file ------------------------------------------------------------
    with open(input_file, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()

            if not line or line.startswith("#"):
                continue

            parts          = line.split()
            url            = parts[0]
            inline_section = parts[1] if len(parts) > 1 else ""

            # Validate URL
            if not SUPPORTED_DOMAINS.search(url):
                print(c(Colors.YELLOW, f"  Skipping non-YouTube/Facebook URL: {url}"))
                skipped += 1
                continue

            total += 1
            print(f"{c(Colors.CYAN, f'[{total}]')} {c(Colors.BOLD, url)}")

            active_section = inline_section or global_sect

            cmd = build_command(
                url=url,
                output_dir=output_dir,
                fmt=fmt,
                quality=DEFAULT_QUALITY,
                active_section=active_section,
                slow_tempo=slow_tempo,
                cookie_file=cookie_file,
            )

            print(c(Colors.YELLOW, f"  -> {' '.join(cmd)}"))

            if not dry_run:
                result = subprocess.run(cmd)
                if result.returncode == 0:
                    print(c(Colors.GREEN, "  [OK] Done"))
                    success += 1
                else:
                    print(c(Colors.RED, "  [FAIL] Failed"))
                    failed += 1
                    failed_urls.append(url)
            else:
                success += 1

            print()

    # --- Summary --------------------------------------------------------------
    print(c(Colors.CYAN, "=" * 40))
    print(c(Colors.BOLD, "  Summary"))
    print(c(Colors.CYAN, "=" * 40))
    print(f"  Total:    {c(Colors.BOLD, str(total))}")
    print(c(Colors.GREEN, f"  Success:  {success}"))
    if failed:
        print(c(Colors.RED, f"  Failed:   {failed}"))
    if skipped:
        print(c(Colors.YELLOW, f"  Skipped:  {skipped}"))

    if failed_urls:
        print()
        print(c(Colors.RED, "Failed URLs:"))
        for u in failed_urls:
            print(c(Colors.RED, f"  [FAIL] {u}"))

    print()
    print(f"  Files saved to: {c(Colors.BOLD, output_dir)}")
    print()

# --- Entry Point --------------------------------------------------------------
def main() -> None:
    args = parse_args()
    check_dependencies()
    process_urls(args)

if __name__ == "__main__":
    main()