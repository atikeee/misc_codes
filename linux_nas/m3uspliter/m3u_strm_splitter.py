#!/usr/bin/env python3
"""
M3U Splitter - Splits a combined M3U file into individual .strm files.
Each pair of lines (EXTINF + URL) becomes one .strm file named after the title.

Usage:
    python3 split_m3u.py <input.m3u> [output_folder]

Example:
    python3 split_m3u.py my_list.m3u ./strm_files
"""

import sys
import os
import re


def extract_title(extinf_line: str) -> str:
    """
    Extract clean title from an #EXTINF line.

    Input:  #EXTINF:-1 group-title="wow",447.[VIXEN] - Crimes of Passion Unleashed | Free at WOW.XXX
    Output: Vixen-Crimes of Passion Unleashed
    """
    # Get everything after the last comma (that's the display name)
    if "," in extinf_line:
        title = extinf_line.split(",", 1)[1]
    else:
        title = extinf_line

    # Remove everything before and including the first '.' if it looks like a number prefix
    # e.g. "447.[VIXEN] - ..." -> "[VIXEN] - ..."
    title = re.sub(r"^\d+\.", "", title.strip())

    # Remove everything after '|' (e.g. "| Free at WOW.XXX")
    if "|" in title:
        title = title.split("|")[0]

    # Remove content inside square brackets (e.g. [VIXEN] -> VIXEN kept as prefix, or drop)
    # Here we strip the brackets but keep the text inside
    title = re.sub(r"\[([^\]]*)\]", r"\1", title)

    # Replace special characters that are invalid in filenames
    title = re.sub(r'[<>:"/\\|?*]', "", title)

    # Collapse multiple spaces/dashes, strip edges
    title = re.sub(r"\s*-\s*", "-", title)
    title = re.sub(r"\s+", " ", title).strip(" -")

    # Remove any remaining non-printable or weird chars
    title = re.sub(r"[^\w\s\-\(\)\.,&']", "", title)

    return title.strip()


def sanitize_filename(name: str) -> str:
    """Final pass to ensure the filename is filesystem-safe."""
    name = name.strip()
    # Truncate to 200 chars to avoid filesystem limits
    return name[:200]


def split_m3u(input_path: str, output_dir: str):
    if not os.path.isfile(input_path):
        print(f"[ERROR] File not found: {input_path}")
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = [line.strip() for line in f.readlines()]

    # Filter out the #EXTM3U header line
    lines = [l for l in lines if l and l != "#EXTM3U"]

    created = 0
    skipped = 0
    i = 0

    while i < len(lines):
        line = lines[i]

        if line.startswith("#EXTINF"):
            extinf_line = line
            # Next non-empty line should be the URL
            i += 1
            url = None
            while i < len(lines):
                if not lines[i].startswith("#"):
                    url = lines[i]
                    break
                i += 1

            if url:
                title = extract_title(extinf_line)
                filename = sanitize_filename(title) + ".strm"
                output_path = os.path.join(output_dir, filename)

                # Handle duplicate filenames
                counter = 1
                base_path = output_path
                while os.path.exists(output_path):
                    name_no_ext = base_path[:-5]
                    output_path = f"{name_no_ext}_{counter}.strm"
                    counter += 1

                with open(output_path, "w", encoding="utf-8") as out:
                    out.write(url + "\n")

                print(f"[OK] {filename}")
                created += 1
            else:
                print(f"[SKIP] No URL found for: {extinf_line[:80]}")
                skipped += 1

        i += 1

    print(f"\nDone! Created: {created} .strm files | Skipped: {skipped}")
    print(f"Output folder: {os.path.abspath(output_dir)}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_file = sys.argv[1]
    output_folder = sys.argv[2] if len(sys.argv) > 2 else "./strm_output"

    split_m3u(input_file, output_folder)